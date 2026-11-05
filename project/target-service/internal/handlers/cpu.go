package handlers

import (
	"crypto/sha256"
	"fmt"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/nishant-ingle/agentic-autoscalar/project/target-service/internal/metrics"
)

type CPULoadRequest struct {
	DurationMs int `form:"duration_ms" json:"duration_ms"` // Duration of burn in milliseconds (default 500ms)
	Concurrency int `form:"concurrency" json:"concurrency"` // Number of worker goroutines burning CPU (default 1)
}

type CPULoadResponse struct {
	Status       string  `json:"status"`
	BurnedTimeMs int64   `json:"burned_time_ms"`
	Concurrency  int     `json:"concurrency"`
	Message      string  `json:"message"`
}

// CPULoad burns CPU cycles across N goroutines for a specified duration in milliseconds.
// @Summary Generate CPU Load
// @Description Spikes CPU across N goroutines for a specified duration to test autoscaling.
// @Tags load
// @Produce json
// @Param duration_ms query int false "Duration of burn in milliseconds (max 30000)" default(500)
// @Param concurrency query int false "Number of worker goroutines (max 16)" default(1)
// @Success 200 {object} CPULoadResponse
// @Router /api/load/cpu [get]
// @Router /api/load/cpu [post]
func CPULoad(c *gin.Context) {
	durationMs := 500
	concurrency := 1

	if val := c.Query("duration_ms"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed > 0 {
			durationMs = parsed
		}
	}
	// Cap duration to 30 seconds max to prevent runaway unmonitored stress
	if durationMs > 30000 {
		durationMs = 30000
	}

	if val := c.Query("concurrency"); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil && parsed > 0 {
			concurrency = parsed
		}
	}
	// Cap concurrency to 16
	if concurrency > 16 {
		concurrency = 16
	}

	burnDuration := time.Duration(durationMs) * time.Millisecond
	deadline := time.Now().Add(burnDuration)
	start := time.Now()

	var wg sync.WaitGroup
	ctx := c.Request.Context()

	for i := 0; i < concurrency; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			var data = []byte(fmt.Sprintf("worker-%d-seed-%d", workerID, time.Now().UnixNano()))
			for time.Now().Before(deadline) {
				select {
				case <-ctx.Done():
					return
				default:
					hash := sha256.Sum256(data)
					data = hash[:]
				}
			}
		}(i)
	}

	wg.Wait()
	elapsed := time.Since(start)

	totalBurnedSec := elapsed.Seconds() * float64(concurrency)
	metrics.SyntheticCPUBurnTime.Add(totalBurnedSec)

	c.JSON(http.StatusOK, CPULoadResponse{
		Status:       "success",
		BurnedTimeMs: elapsed.Milliseconds(),
		Concurrency:  concurrency,
		Message:      fmt.Sprintf("Successfully sustained CPU load for %v on %d worker(s)", elapsed, concurrency),
	})
}
