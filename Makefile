# ─────────────────────────────────────────────────────────
#  ETFInfo Docker Makefile
#  이미지: skcha/etfinfo-backend, skcha/etfinfo-frontend
#  태그:   YYYYMMDD-HHMMSS  +  latest
# ─────────────────────────────────────────────────────────

BACKEND_IMAGE  := skcha/etfinfo-backend
FRONTEND_IMAGE := skcha/etfinfo-frontend

# 빌드 시점 datetime 태그 (예: 20260429-103156)
TAG := $(shell date +%Y%m%d-%H%M%S)

BACKEND_DIR  := ./backend
FRONTEND_DIR := ./frontend

.PHONY: all build build-backend build-frontend \
        push push-backend push-frontend \
        release help

# ── 기본 타겟
all: build

# ── 전체 빌드
build: build-backend build-frontend

build-backend:
	@echo "▶ Building backend  $(BACKEND_IMAGE):$(TAG)"
	docker build -t $(BACKEND_IMAGE):$(TAG) -t $(BACKEND_IMAGE):latest $(BACKEND_DIR)
	@echo "✅ Backend built: $(BACKEND_IMAGE):$(TAG)"

build-frontend:
	@echo "▶ Building frontend $(FRONTEND_IMAGE):$(TAG)"
	docker build -t $(FRONTEND_IMAGE):$(TAG) -t $(FRONTEND_IMAGE):latest $(FRONTEND_DIR)
	@echo "✅ Frontend built: $(FRONTEND_IMAGE):$(TAG)"

# ── 전체 푸시
push: push-backend push-frontend

push-backend:
	@echo "▶ Pushing backend  $(BACKEND_IMAGE):$(TAG)"
	docker push $(BACKEND_IMAGE):$(TAG)
	docker push $(BACKEND_IMAGE):latest
	@echo "✅ Backend pushed: $(BACKEND_IMAGE):$(TAG)"

push-frontend:
	@echo "▶ Pushing frontend $(FRONTEND_IMAGE):$(TAG)"
	docker push $(FRONTEND_IMAGE):$(TAG)
	docker push $(FRONTEND_IMAGE):latest
	@echo "✅ Frontend pushed: $(FRONTEND_IMAGE):$(TAG)"

# ── 빌드 + 푸시 한 번에
release: build push
	@echo ""
	@echo "🚀 Release complete!"
	@echo "   $(BACKEND_IMAGE):$(TAG)"
	@echo "   $(FRONTEND_IMAGE):$(TAG)"

# ─────────────────────────────────────────────────────────
#  K8s 배포 (Kustomize)
#  ENV: dev (기본값) | prod
# ─────────────────────────────────────────────────────────

ENV ?= dev

# 호스트 IP 자동 감지
# 1. host.docker.internal (Docker Desktop Mac/Win)
# 2. Kind Gateway (IPv4)
# 3. Default Route
# 4. Fallback
HOST_IP := $(shell \
  (docker run --rm busybox nslookup host.docker.internal 2>/dev/null | grep "Address:" | tail -n1 | awk '{print $$2}' | grep .) \
  || (getent hosts host.docker.internal 2>/dev/null | awk '{print $$1}' | grep .) \
  || (docker network inspect kind 2>/dev/null | jq -r '.[0].IPAM.Config[] | select(.Subnet | contains(".")) | .Gateway' | grep .) \
  || (ip route get 1 2>/dev/null | awk '{print $$7; exit}' | grep .) \
  || echo "127.0.0.1")

# 이미지 태그를 overlay kustomization에 인라인 패치로 주입
deploy:
	@echo "▶ Deploying to k8s (env=$(ENV), tag=$(TAG), host_ip=$(HOST_IP))"
	kustomize build k8s/overlays/$(ENV) \
	  | sed 's|skcha/etfinfo-backend:latest|$(BACKEND_IMAGE):$(TAG)|g' \
	  | sed 's|skcha/etfinfo-frontend:latest|$(FRONTEND_IMAGE):$(TAG)|g' \
	  | sed 's|192.168.65.2|$(HOST_IP)|g' \
	  | kubectl apply -f -
	@echo "✅ Deployed (env=$(ENV)) — $(BACKEND_IMAGE):$(TAG)"

# dry-run: 실제 적용 없이 diff만 확인
deploy-diff:
	@echo "▶ Diff (env=$(ENV), tag=$(TAG), host_ip=$(HOST_IP))"
	kustomize build k8s/overlays/$(ENV) \
	  | sed 's|skcha/etfinfo-backend:latest|$(BACKEND_IMAGE):$(TAG)|g' \
	  | sed 's|skcha/etfinfo-frontend:latest|$(FRONTEND_IMAGE):$(TAG)|g' \
	  | sed 's|192.168.65.2|$(HOST_IP)|g' \
	  | kubectl diff -f -

# 삭제
undeploy:
	@echo "▶ Removing from k8s (env=$(ENV))"
	kustomize build k8s/overlays/$(ENV) | kubectl delete -f -

# 호스트 IP 확인
show-host-ip:
	@echo "Host IP: $(HOST_IP)"

# ── 도움말
help:
	@echo ""
	@echo "Usage: make [target] [TAG=<tag>] [ENV=dev|prod]"
	@echo ""
	@echo "Build & Push:"
	@echo "  build            백엔드 + 프론트엔드 빌드 (datetime 태그 자동 생성)"
	@echo "  build-backend    백엔드만 빌드"
	@echo "  build-frontend   프론트엔드만 빌드"
	@echo "  push             백엔드 + 프론트엔드 Docker Hub 푸시"
	@echo "  push-backend     백엔드만 푸시"
	@echo "  push-frontend    프론트엔드만 푸시"
	@echo "  release          빌드 + 푸시 한 번에"
	@echo ""
	@echo "K8s (Kustomize):"
	@echo "  deploy           k8s에 배포         (기본: ENV=dev)"
	@echo "  deploy-diff      배포 전 diff 확인"
	@echo "  undeploy         k8s에서 리소스 제거"
	@echo ""
	@echo "Examples:"
	@echo "  make build                        # 자동 datetime 태그로 빌드"
	@echo "  make release                      # 빌드 + 푸시"
	@echo "  make release TAG=v1.0.0           # 커스텀 태그로 빌드+푸시"
	@echo "  make deploy ENV=dev TAG=v1.0.0    # dev 환경에 배포"
	@echo "  make deploy ENV=prod TAG=v1.0.0   # prod 환경에 배포"
	@echo "  make deploy-diff ENV=prod         # prod 배포 전 변경사항 확인"
	@echo ""
