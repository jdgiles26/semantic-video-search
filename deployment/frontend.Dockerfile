# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY dashboard/package*.json ./

# Install dependencies (using npm install since we don't have package-lock.json)
RUN npm install

# Copy source code
COPY dashboard/ ./

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY deployment/nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
