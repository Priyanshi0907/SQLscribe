# Multi-stage build: compile the Vite/React app, then serve the static
# output with nginx — the container never runs `npm run dev`.
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# VITE_API_BASE is baked into the JS bundle at build time (Vite env vars
# are compile-time, not runtime) — override it via --build-arg when the
# backend isn't reachable at the default http://127.0.0.1:8000, e.g.
# `docker build --build-arg VITE_API_BASE=https://api.example.com .`
ARG VITE_API_BASE=http://127.0.0.1:8000
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O- http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
