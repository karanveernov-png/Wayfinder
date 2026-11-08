FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite bakes these in at BUILD time, not runtime - a container started with
# -e/--env-file has no effect on them. Must be passed as --build-arg (or via
# docker-compose's build.args, see docker-compose.yml) pointing at your real
# deployed backend URL and Supabase project; left unset, the build silently
# falls back to the http://localhost:8000 dev default and an unconfigured
# Supabase client, which only "works" when frontend and backend share a host.
ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_MAPTILER_API_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_MAPTILER_API_KEY=$VITE_MAPTILER_API_KEY
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
