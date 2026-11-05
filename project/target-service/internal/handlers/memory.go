package handlers

import (
	"fmt"
	"net/http"
	"runtime"
	"strconv"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/nishant-ingle/agentic-autoscalar/project/target-service/internal/metrics"
)

var (
	memStoreMutex sync.Mutex
	memStore      [][]byte
)

type MemoryLoadResponse struct {
	Status           string `json:"status"`
	AllocatedMB      int    `json:"allocated_mb"`
	TotalRetainedMB  int    `json:"total_retained_mb"`
	HeapAllocBytes   uint64 `json:"heap_alloc_bytes"`
	Message          string `json:"message"`
}

// MemoryAllocate allocates chunks of memory to simulate memory footprint growth.
// @Summary Allocate Memory
// @Description Artificially inflates the pod's memory working set for autoscaling tests.
// @Tags load
// @Produce json
// @Param mb query int false "Megabytes to allocate (max 1024)" default(50)
// @Success 200 {object} MemoryLoadResponse
// @Router /api/load/memory/allocate [post]
func MemoryAllocate(c *gin.Context) {
	mb := 50
	if val := c.Query("mb"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed > 0 {
			mb = parsed
		}
	}
	if mb > 1024 {
		mb = 1024 // safety ceiling 1GB
	}

	memStoreMutex.Lock()
	defer memStoreMutex.Unlock()

	// 1 MB buffer
	chunkSize := 1024 * 1024
	for i := 0; i < mb; i++ {
		chunk := make([]byte, chunkSize)
		for j := range chunk {
			chunk[j] = byte(j % 255)
		}
		memStore = append(memStore, chunk)
	}

	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	totalMB := len(memStore)
	metrics.SyntheticMemoryAllocated.Set(float64(totalMB * chunkSize))

	c.JSON(http.StatusOK, MemoryLoadResponse{
		Status:          "success",
		AllocatedMB:     mb,
		TotalRetainedMB: totalMB,
		HeapAllocBytes:  m.Alloc,
		Message:         fmt.Sprintf("Allocated %d MB, total held: %d MB", mb, totalMB),
	})
}

// MemoryRelease frees all synthetically allocated memory buffers and triggers GC.
// @Summary Release Memory
// @Description Clears synthetic memory buffers and forces garbage collection.
// @Tags load
// @Produce json
// @Success 200 {object} MemoryLoadResponse
// @Router /api/load/memory/release [post]
func MemoryRelease(c *gin.Context) {
	memStoreMutex.Lock()
	memStore = nil
	metrics.SyntheticMemoryAllocated.Set(0)
	memStoreMutex.Unlock()

	runtime.GC()

	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	c.JSON(http.StatusOK, MemoryLoadResponse{
		Status:          "released",
		AllocatedMB:     0,
		TotalRetainedMB: 0,
		HeapAllocBytes:  m.Alloc,
		Message:         "Cleared all synthetic memory buffers and executed runtime.GC()",
	})
}
