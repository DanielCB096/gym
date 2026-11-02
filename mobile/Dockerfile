FROM node:24-alpine AS build

WORKDIR /app

COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci

COPY mobile/ ./
ARG EXPO_PUBLIC_API_URL=http://localhost:8010
ENV EXPO_PUBLIC_API_URL=${EXPO_PUBLIC_API_URL} \
    EXPO_NO_TELEMETRY=1

RUN npx expo export --platform web

FROM nginx:alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
