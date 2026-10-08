# Build context must be the repo root: docker build -f nginx/Dockerfile .
FROM node:20-alpine AS builder

WORKDIR /build

# Install root-level deps (concurrently)
COPY package.json package-lock.json ./
RUN npm ci

# Install each frontend's deps with its own lockfile
COPY frontend/student/package.json frontend/student/package-lock.json ./frontend/student/
COPY frontend/staff/package.json frontend/staff/package-lock.json ./frontend/staff/
COPY frontend/admin/package.json frontend/admin/package-lock.json ./frontend/admin/
RUN npm ci --prefix frontend/student && \
    npm ci --prefix frontend/staff && \
    npm ci --prefix frontend/admin

# Copy source and build all three apps
COPY frontend/ ./frontend/
RUN npm run build

FROM nginx:1.25-alpine
COPY --from=builder /build/frontend/student/dist /usr/share/nginx/html/student
COPY --from=builder /build/frontend/staff/dist   /usr/share/nginx/html/staff
COPY --from=builder /build/frontend/admin/dist   /usr/share/nginx/html/admin
COPY nginx/nginx.prod.conf /etc/nginx/nginx.conf
