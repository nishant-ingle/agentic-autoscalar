package metrics

import (
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	// HTTPRequestsTotal tracks the cumulative number of HTTP requests processed.
	HTTPRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "workload",
			Subsystem: "http",
			Name:      "requests_total",
			Help:      "Total number of HTTP requests processed, labeled by status code, method, and path pattern.",
		},
		[]string{"method", "path", "status"},
	)

	// HTTPRequestDuration tracks latency distribution across handlers.
	HTTPRequestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: "workload",
			Subsystem: "http",
			Name:      "request_duration_seconds",
			Help:      "Latency histogram of HTTP requests in seconds.",
			Buckets:   []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0},
		},
		[]string{"method", "path", "status"},
	)

	// InFlightRequests monitors active concurrent requests.
	InFlightRequests = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Namespace: "workload",
			Subsystem: "http",
			Name:      "in_flight_requests",
			Help:      "Current number of active in-flight HTTP requests.",
		},
	)

	// SyntheticCPUBurnTime records total duration spent in artificial CPU burning loops.
	SyntheticCPUBurnTime = prometheus.NewCounter(
		prometheus.CounterOpts{
			Namespace: "workload",
			Subsystem: "synthetic",
			Name:      "cpu_burn_seconds_total",
			Help:      "Total seconds spent executing artificial CPU stress routines.",
		},
	)

	// SyntheticMemoryAllocated tracks current artificial heap allocation in bytes.
	SyntheticMemoryAllocated = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Namespace: "workload",
			Subsystem: "synthetic",
			Name:      "allocated_memory_bytes",
			Help:      "Current memory artificially allocated in bytes.",
		},
	)
)

func init() {
	prometheus.MustRegister(
		HTTPRequestsTotal,
		HTTPRequestDuration,
		InFlightRequests,
		SyntheticCPUBurnTime,
		SyntheticMemoryAllocated,
	)
}

// GinMetricsMiddleware wraps Gin handlers to collect golden signals (Rate, Errors, Duration, Saturation).
func GinMetricsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Do not instrument the /metrics endpoint itself to avoid recursion/skew
		if c.Request.URL.Path == "/metrics" || c.Request.URL.Path == "/healthz" || c.Request.URL.Path == "/readyz" {
			c.Next()
			return
		}

		InFlightRequests.Inc()
		startTime := time.Now()

		c.Next()

		duration := time.Since(startTime).Seconds()
		InFlightRequests.Dec()

		path := c.FullPath()
		if path == "" {
			path = "unknown"
		}
		status := strconv.Itoa(c.Writer.Status())
		method := c.Request.Method

		HTTPRequestsTotal.WithLabelValues(method, path, status).Inc()
		HTTPRequestDuration.WithLabelValues(method, path, status).Observe(duration)
	}
}

// PrometheusHandler exposes the Prometheus standard registry handler.
func PrometheusHandler() gin.HandlerFunc {
	h := promhttp.Handler()
	return func(c *gin.Context) {
		h.ServeHTTP(c.Writer, c.Request)
	}
}
