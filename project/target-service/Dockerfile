# Build stage
FROM golang:1.26-alpine AS builder

WORKDIR /app

# Install git and ca-certificates
RUN apk add --no-cache git ca-certificates

# Pre-copy go.mod and go.sum for better cache utilization
COPY go.mod ./
# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build static binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-w -s" -o /bin/target-service ./cmd/server/main.go || \
    CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /bin/target-service ./cmd/server/main.go

# Runtime stage
FROM alpine:3.20

# Install ca-certificates and curl for diagnostic probes if needed
RUN apk --no-cache add ca-certificates curl tzdata && \
    addgroup -g 10001 appgroup && \
    adduser -u 10001 -G appgroup -D -s /bin/sh appuser

WORKDIR /home/appuser

COPY --from=builder /bin/target-service /usr/local/bin/target-service

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8080/healthz || exit 1

ENTRYPOINT ["/usr/local/bin/target-service"]
