FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# The image's entrypoint renders /etc/nginx/templates/*.template into conf.d with
# envsubst, substituting only variables defined in the container environment.
# Source: https://github.com/nginxinc/docker-nginx/blob/master/entrypoint/20-envsubst-on-templates.sh
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
RUN mkdir -p /usr/share/nginx/errors && touch /usr/share/nginx/errors/empty
