# ==============================================================================
# Production frontend image — multi-stage: ng build → static nginx.
# Used by docker-compose.prod.yml. Dev keeps the ng-serve bind-mount container.
# ==============================================================================
FROM node:20-alpine AS build

WORKDIR /app

# Dependency layer (cached unless package*.json changes)
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npx ng build --configuration production

# --- Runtime: static files behind nginx -------------------------------------
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/iway-support-ui/browser /usr/share/nginx/html

EXPOSE 80
