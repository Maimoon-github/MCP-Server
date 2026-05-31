# Deployment Guide

> Docker, Kubernetes, and cloud deployment strategies for the Universal MCP Server.

---

## Table of Contents

1. [Docker Deployment](#docker-deployment)
2. [Docker Compose](#docker-compose)
3. [Kubernetes](#kubernetes)
4. [Cloud Platforms](#cloud-platforms)
5. [Reverse Proxy & SSL](#reverse-proxy--ssl)
6. [Monitoring & Observability](#monitoring--observability)
7. [Security Hardening](#security-hardening)

---

## Docker Deployment

### Quick Start

```bash
# Build the image
docker build -t universal-mcp:latest .

# Run STDIO mode (for local AI hosts)
docker run -i --rm universal-mcp:latest

# Run HTTP mode with environment variables
docker run -d   --name universal-mcp   -p 3000:3000   -e MCP_TRANSPORT=http   -e MCP_HTTP_PORT=3000   -e MCP_AUTH_MODE=api_key   -e MCP_API_KEY=your-secret-key   -e MCP_SANDBOX_PATHS=/data   -v /host/data:/data:ro   universal-mcp:latest
```

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir build &&     python -m build --wheel

FROM python:3.12-slim

# Security: Run as non-root user
RUN groupadd -r mcp && useradd -r -g mcp mcp

WORKDIR /app

# Install runtime dependencies
COPY --from=builder /app/dist/*.whl ./
RUN pip install --no-cache-dir *.whl && rm *.whl

# Create log directory
RUN mkdir -p /var/log/universal_mcp && chown mcp:mcp /var/log/universal_mcp

# Copy config
COPY mcp_config.json /app/
COPY .env.example /app/.env

# Switch to non-root
USER mcp

# Expose HTTP port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3   CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')" || exit 1

# Default: STDIO mode (override with --transport http)
ENTRYPOINT ["python", "-m", "universal_mcp"]
CMD ["--transport", "stdio"]
```

### Multi-Stage Build Benefits

| Stage | Purpose | Size Impact |
|-------|---------|-------------|
| `builder` | Compile wheels | Discarded |
| `runtime` | Minimal image with only runtime deps | ~150MB vs ~500MB |

---

## Docker Compose

### Local Development Stack

```yaml
# docker-compose.yml
version: "3.8"

services:
  universal-mcp:
    build: .
    container_name: universal-mcp
    ports:
      - "3000:3000"
    environment:
      - MCP_TRANSPORT=http
      - MCP_HTTP_PORT=3000
      - MCP_LOG_LEVEL=INFO
      - MCP_AUTH_MODE=api_key
      - MCP_API_KEY=${MCP_API_KEY}
      - MCP_SANDBOX_PATHS=/data,/tmp
      - MCP_RATE_LIMIT_RPM=120
    volumes:
      - ./data:/data:ro
      - mcp_logs:/var/log/universal_mcp
    networks:
      - mcp_network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Optional: Redis for rate limiting
  redis:
    image: redis:7-alpine
    container_name: mcp-redis
    volumes:
      - redis_data:/data
    networks:
      - mcp_network
    restart: unless-stopped

  # Optional: Prometheus for metrics
  prometheus:
    image: prom/prometheus:latest
    container_name: mcp-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    networks:
      - mcp_network

volumes:
  mcp_logs:
  redis_data:

networks:
  mcp_network:
    driver: bridge
```

### Production Compose

```yaml
# docker-compose.prod.yml
version: "3.8"

services:
  universal-mcp:
    image: your-registry/universal-mcp:latest
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
    environment:
      - MCP_TRANSPORT=http
      - MCP_HTTP_PORT=3000
      - MCP_AUTH_MODE=oauth2
      - MCP_OAUTH2_ISSUER=https://auth.yourcompany.com
      - MCP_RATE_LIMIT_RPM=60
      - MCP_LOG_LEVEL=WARNING
    secrets:
      - mcp_api_key
    networks:
      - traefik_public
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.mcp.rule=Host(\`mcp.yourcompany.com\`)"
      - "traefik.http.routers.mcp.tls=true"
      - "traefik.http.routers.mcp.tls.certresolver=letsencrypt"

secrets:
  mcp_api_key:
    external: true

networks:
  traefik_public:
    external: true
```

---

## Kubernetes

### Deployment Manifest

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: universal-mcp
  namespace: mcp
  labels:
    app: universal-mcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: universal-mcp
  template:
    metadata:
      labels:
        app: universal-mcp
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: universal-mcp
          image: your-registry/universal-mcp:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 3000
              name: http
          env:
            - name: MCP_TRANSPORT
              value: "http"
            - name: MCP_HTTP_PORT
              value: "3000"
            - name: MCP_AUTH_MODE
              value: "bearer"
            - name: MCP_API_KEY
              valueFrom:
                secretKeyRef:
                  name: mcp-secrets
                  key: api-key
            - name: MCP_LOG_LEVEL
              value: "INFO"
            - name: MCP_RATE_LIMIT_RPM
              value: "120"
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /ready
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          volumeMounts:
            - name: logs
              mountPath: /var/log/universal_mcp
            - name: data
              mountPath: /data
              readOnly: true
      volumes:
        - name: logs
          emptyDir: {}
        - name: data
          persistentVolumeClaim:
            claimName: mcp-data-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: universal-mcp
  namespace: mcp
spec:
  selector:
    app: universal-mcp
  ports:
    - port: 80
      targetPort: 3000
      name: http
  type: ClusterIP
---
apiVersion: v1
kind: Secret
metadata:
  name: mcp-secrets
  namespace: mcp
type: Opaque
stringData:
  api-key: "your-secure-api-key-here"
```

### Horizontal Pod Autoscaler

```yaml
# k8s-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: universal-mcp-hpa
  namespace: mcp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: universal-mcp
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
```

### Ingress with TLS

```yaml
# k8s-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: universal-mcp-ingress
  namespace: mcp
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - mcp.yourcompany.com
      secretName: mcp-tls-secret
  rules:
    - host: mcp.yourcompany.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: universal-mcp
                port:
                  number: 80
```

---

## Cloud Platforms

### AWS ECS (Fargate)

```json
// ecs-task-definition.json
{
  "family": "universal-mcp",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "universal-mcp",
      "image": "your-registry/universal-mcp:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 3000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "MCP_TRANSPORT", "value": "http"},
        {"name": "MCP_HTTP_PORT", "value": "3000"},
        {"name": "MCP_AUTH_MODE", "value": "api_key"}
      ],
      "secrets": [
        {
          "name": "MCP_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:mcp-api-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/universal-mcp",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c "import urllib.request; urllib.request.urlopen(\"http://localhost:3000/health\")""],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      }
    }
  ]
}
```

### Google Cloud Run

```bash
# Deploy to Cloud Run
gcloud run deploy universal-mcp   --image gcr.io/PROJECT/universal-mcp:latest   --platform managed   --region us-central1   --port 3000   --env-vars-file env.yaml   --allow-unauthenticated   --max-instances 10   --min-instances 1   --memory 512Mi   --cpu 1
```

```yaml
# env.yaml
MCP_TRANSPORT: "http"
MCP_HTTP_PORT: "3000"
MCP_AUTH_MODE: "bearer"
MCP_LOG_LEVEL: "INFO"
MCP_RATE_LIMIT_RPM: "60"
```

### Azure Container Instances

```bash
az container create   --resource-group myResourceGroup   --name universal-mcp   --image your-registry/universal-mcp:latest   --ports 3000   --environment-variables MCP_TRANSPORT=http MCP_HTTP_PORT=3000   --secure-environment-variables MCP_API_KEY=secret-key   --cpu 1   --memory 1   --restart-policy OnFailure
```

---

## Reverse Proxy & SSL

### Nginx Configuration

```nginx
# /etc/nginx/sites-available/mcp
server {
    listen 443 ssl http2;
    server_name mcp.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/mcp.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.yourcompany.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=mcp:10m rate=10r/s;
    limit_req zone=mcp burst=20 nodelay;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    location /health {
        proxy_pass http://localhost:3000/health;
        access_log off;
    }
}
```

### Traefik (Docker Swarm / K8s)

```yaml
# traefik-dynamic.yml
http:
  routers:
    mcp:
      rule: "Host(\`mcp.yourcompany.com\`)"
      service: mcp-service
      tls:
        certResolver: letsencrypt
      middlewares:
        - mcp-ratelimit
        - mcp-auth

  services:
    mcp-service:
      loadBalancer:
        servers:
          - url: "http://universal-mcp:3000"
        healthCheck:
          path: /health
          interval: 10s

  middlewares:
    mcp-ratelimit:
      rateLimit:
        average: 100
        burst: 50

    mcp-auth:
      forwardAuth:
        address: "http://auth-service:8080/verify"
```

---

## Monitoring & Observability

### Prometheus Metrics

The server exposes metrics at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `mcp_requests_total` | Counter | Total requests by method |
| `mcp_request_duration_seconds` | Histogram | Request latency |
| `mcp_tools_called_total` | Counter | Tool invocations by name |
| `mcp_resources_read_total` | Counter | Resource reads by URI |
| `mcp_prompts_rendered_total` | Counter | Prompt renders by name |
| `mcp_errors_total` | Counter | Errors by type |
| `mcp_active_connections` | Gauge | Current SSE/WebSocket connections |

### Grafana Dashboard

```json
// grafana-dashboard.json (excerpt)
{
  "dashboard": {
    "title": "Universal MCP Server",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(mcp_requests_total[5m])",
            "legendFormat": "{{method}}"
          }
        ]
      },
      {
        "title": "Tool Usage",
        "targets": [
          {
            "expr": "topk(10, rate(mcp_tools_called_total[1h]))",
            "legendFormat": "{{tool_name}}"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(mcp_errors_total[5m])",
            "legendFormat": "{{error_type}}"
          }
        ]
      }
    ]
  }
}
```

### Logging with Loki

```yaml
# promtail-config.yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: mcp-logs
    static_configs:
      - targets:
          - localhost
        labels:
          job: universal-mcp
          __path__: /var/log/universal_mcp/*.log
```

---

## Security Hardening

### Checklist

- [ ] Run container as non-root user (`USER mcp` in Dockerfile)
- [ ] Use read-only root filesystem (`readOnlyRootFilesystem: true` in K8s)
- [ ] Drop all capabilities (`drop: [ALL]` in K8s securityContext)
- [ ] Enable seccomp profile (`seccompProfile: {type: RuntimeDefault}`)
- [ ] Use secrets management (K8s Secrets, AWS Secrets Manager, Vault)
- [ ] Enable network policies (restrict ingress/egress in K8s)
- [ ] Configure resource limits (prevent DoS via resource exhaustion)
- [ ] Enable audit logging (immutable logs to SIEM)
- [ ] Use TLS 1.2+ only (disable SSLv3, TLS 1.0, TLS 1.1)
- [ ] Implement rate limiting (per-client token bucket)
- [ ] Set up WAF rules (block SQL injection, XSS in HTTP mode)
- [ ] Regular image scanning (Trivy, Snyk, Clair)

### Pod Security Standards (PSS)

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
      - ALL
```

---

*Last updated: 2026-06-01*
