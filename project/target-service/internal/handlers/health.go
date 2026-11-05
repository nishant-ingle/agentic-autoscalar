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
// @Summary Liveness Probe
// @Description Returns 200 OK if the server is running.
// @Tags health
// @Produce json
// @Success 200 {object} HealthResponse
// @Router /healthz [get]
// @Router /livez [get]
func Healthz(c *gin.Context) {
	hostname, _ := os.Hostname()
	c.JSON(http.StatusOK, HealthResponse{
		Status:   "UP",
		Hostname: hostname,
		Version:  "1.0.0",
	})
}

// Readyz responds to readiness probes.
// @Summary Readiness Probe
// @Description Returns 200 OK if the server is ready to accept traffic.
// @Tags health
// @Produce json
// @Success 200 {object} HealthResponse
// @Router /readyz [get]
func Readyz(c *gin.Context) {
	hostname, _ := os.Hostname()
	c.JSON(http.StatusOK, HealthResponse{
		Status:   "READY",
		Hostname: hostname,
		Version:  "1.0.0",
	})
}
