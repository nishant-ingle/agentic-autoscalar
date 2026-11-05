package handlers

import (
	"crypto/sha256"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

type WorkloadResponse struct {
	Hostname       string `json:"hostname"`
	Timestamp      string `json:"timestamp"`
	ComputationRounds int `json:"computation_rounds"`
	SleepDelayMs   int64  `json:"sleep_delay_ms"`
	ResultChecksum string `json:"result_checksum"`
}

// WorkloadMixed simulates a standard microservice processing payload (CPU + I/O).
// @Summary Simulate Mixed Workload
// @Description Simulates a standard API call with adjustable I/O sleep delay and CPU hashing.
// @Tags load
// @Produce json
// @Param rounds query int false "Number of SHA256 hashing rounds (max 500000)" default(20000)
// @Param delay_ms query int false "Simulated I/O sleep delay in ms (max 5000)" default(10)
// @Success 200 {object} WorkloadResponse
// @Router /api/workload [get]
// @Router /api/workload [post]
func WorkloadMixed(c *gin.Context) {
	rounds := 20000
	if val := c.Query("rounds"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed > 0 {
			rounds = parsed
		}
	}
	if rounds > 500000 {
		rounds = 500000
	}

	delayMs := int64(10)
	if val := c.Query("delay_ms"); val != "" {
		if parsed, err := strconv.ParseInt(val, 10, 64); err == nil && parsed >= 0 {
			delayMs = parsed
		}
	}
	if delayMs > 5000 {
		delayMs = 5000
	}

	// 1. I/O Delay simulation (database, upstream microservice call)
	if delayMs > 0 {
		// add small jitter
		jitter := rand.Int63n(5)
		time.Sleep(time.Duration(delayMs+jitter) * time.Millisecond)
	}

	// 2. CPU Workload
	data := []byte("seed-data-for-autoscaler-workload")
	for i := 0; i < rounds; i++ {
		hash := sha256.Sum256(data)
		data = hash[:]
	}

	hostname, _ := os.Hostname()

	c.JSON(http.StatusOK, WorkloadResponse{
		Hostname:          hostname,
		Timestamp:         time.Now().UTC().Format(time.RFC3339Nano),
		ComputationRounds: rounds,
		SleepDelayMs:      delayMs,
		ResultChecksum:    fmt.Sprintf("%x", data[:8]),
	})
}
