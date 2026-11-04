package handlers

import (
	"net/http"
	"os"

	"github.com/gin-gonic/gin"
)

type HealthResponse struct {
	Status   string `json:"status"`
	Hostname string `json:"hostname"`
	Version  string `json:"version"`
}

// Healthz responds to liveness probes.
func Healthz(c *gin.Context) {
	hostname, _ := os.Hostname()
	c.JSON(http.StatusOK, HealthResponse{
		Status:   "UP",
		Hostname: hostname,
		Version:  "1.0.0",
	})
}

// Readyz responds to readiness probes.
func Readyz(c *gin.Context) {
	hostname, _ := os.Hostname()
	c.JSON(http.StatusOK, HealthResponse{
		Status:   "READY",
		Hostname: hostname,
		Version:  "1.0.0",
	})
}
