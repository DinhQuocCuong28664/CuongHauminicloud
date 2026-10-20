FROM nginx:1.30.6-alpine

LABEL org.opencontainers.image.title="myminicloud-proxy" \
      org.opencontainers.image.description="MyMiniCloud API gateway / load balancer: nginx (route, round robin, rate limit, JSON log, HTTPS on EC2)" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

# Routing config is baked into the image so EC2 only needs to pull it from Docker Hub
COPY nginx.conf /etc/nginx/nginx.conf
COPY snippets/ /etc/nginx/snippets/
COPY conf.d/default.conf /etc/nginx/conf.d/default.conf
# Webroot directory for Let's Encrypt (the certbot-www volume is mounted on EC2)
RUN mkdir -p /var/www/certbot

EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
