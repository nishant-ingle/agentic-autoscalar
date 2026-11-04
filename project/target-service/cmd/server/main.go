package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/nishant-ingle/agentic-autoscaler/target-service/internal/handlers"
	"github.com/nishant-ingle/agentic-autoscaler/target-service/internal/metrics"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	ginMode := os.Getenv("GIN_MODE")
	if ginMode == "" {
		gin.SetMode(gin.ReleaseMode)
	}

	router := gin.New()
	router.Use(gin.Recovery())
	router.Use(metrics.GinMetricsMiddleware())

	// Standard health and observability routes
	router.GET("/healthz", handlers.Healthz)
	router.GET("/readyz", handlers.Readyz)
	router.GET("/livez", handlers.Healthz)
	router.GET("/metrics", metrics.PrometheusHandler())

	// Synthetic load generation routes (for stress-testing autoscaling)
	api := router.Group("/api")
	{
		// CPU stress testing
		api.GET("/load/cpu", handlers.CPULoad)
		api.POST("/load/cpu", handlers.CPULoad)

		// Memory stress testing
		api.POST("/load/memory/allocate", handlers.MemoryAllocate)
		api.POST("/load/memory/release", handlers.MemoryRelease)

		// Representative microservice workload
		api.GET("/workload", handlers.WorkloadMixed)
		api.POST("/workload", handlers.WorkloadMixed)
	}

	server := &http.Server{
		Addr:         fmt.Sprintf(":%s", port),
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 35 * time.Second, // accommodate long cpu load tests up to 30s
		IdleTimeout:  60 * time.Second,
	}

	// Run server in goroutine
	go func() {
		log.Printf("Target microservice starting on port %s (GIN_MODE=%s)...", port, gin.Mode())
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed to listen: %v", err)
		}
	}()

	// Graceful shutdown on SIGTERM / SIGINT for Kubernetes pod termination
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	sig := <-quit
	log.Printf("Received signal %s. Initiating graceful shutdown...", sig)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited gracefully.")
}
