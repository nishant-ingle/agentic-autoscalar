package handlers_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/nishant-ingle/agentic-autoscaler/target-service/internal/handlers"
	"github.com/nishant-ingle/agentic-autoscaler/target-service/internal/metrics"
)

func setupTestRouter() *gin.Engine {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(metrics.GinMetricsMiddleware())

	router.GET("/healthz", handlers.Healthz)
	router.GET("/readyz", handlers.Readyz)
	router.GET("/metrics", metrics.PrometheusHandler())
	router.GET("/api/load/cpu", handlers.CPULoad)
	router.POST("/api/load/memory/allocate", handlers.MemoryAllocate)
	router.POST("/api/load/memory/release", handlers.MemoryRelease)
	router.GET("/api/workload", handlers.WorkloadMixed)

	return router
}

func TestHealthCheck(t *testing.T) {
	router := setupTestRouter()

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/healthz", nil)
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", w.Code)
	}

	var res handlers.HealthResponse
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("Failed to parse JSON: %v", err)
	}
	if res.Status != "UP" {
		t.Errorf("Expected status UP, got %s", res.Status)
	}
}

func TestWorkloadCompute(t *testing.T) {
	router := setupTestRouter()

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/workload?rounds=100&delay_ms=0", nil)
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", w.Code)
	}

	var res handlers.WorkloadResponse
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("Failed to parse JSON: %v", err)
	}
	if res.ComputationRounds != 100 {
		t.Errorf("Expected 100 rounds, got %d", res.ComputationRounds)
	}
}

func TestCPULoadBurn(t *testing.T) {
	router := setupTestRouter()

	w := httptest.NewRecorder()
	req, _ := http.NewRequest(http.MethodGet, "/api/load/cpu?duration_ms=50&concurrency=1", nil)
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", w.Code)
	}
}

func TestMetricsEndpoint(t *testing.T) {
	router := setupTestRouter()

	// Trigger a request to generate metrics
	w1 := httptest.NewRecorder()
	req1, _ := http.NewRequest(http.MethodGet, "/api/workload?rounds=10&delay_ms=0", nil)
	router.ServeHTTP(w1, req1)

	// Fetch /metrics
	w2 := httptest.NewRecorder()
	req2, _ := http.NewRequest(http.MethodGet, "/metrics", nil)
	router.ServeHTTP(w2, req2)

	if w2.Code != http.StatusOK {
		t.Fatalf("Expected status 200 for /metrics, got %d", w2.Code)
	}

	body := w2.Body.String()
	if !containsString(body, "workload_http_requests_total") {
		t.Errorf("Expected metrics to contain workload_http_requests_total")
	}
}

func containsString(haystack, needle string) bool {
	return len(haystack) > 0 && len(needle) > 0 && (stringSearch(haystack, needle) >= 0)
}

func stringSearch(s, substr string) int {
	for i := 0; i+len(substr) <= len(s); i++ {
		if s[i:i+len(substr)] == substr {
			return i
		}
	}
	return -1
}
