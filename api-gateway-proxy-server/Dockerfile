FROM nginx:1.30.6-alpine

LABEL org.opencontainers.image.title="myminicloud-proxy" \
      org.opencontainers.image.description="MyMiniCloud API gateway / load balancer: nginx (route, round robin, rate limit, JSON log, HTTPS trên EC2)" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

# Cấu hình định tuyến đóng gói sẵn trong image để EC2 chỉ cần kéo image từ Docker Hub
COPY nginx.conf /etc/nginx/nginx.conf
COPY snippets/ /etc/nginx/snippets/
COPY conf.d/default.conf /etc/nginx/conf.d/default.conf
# Thư mục webroot cho Let's Encrypt (trên EC2 được gắn volume certbot-www)
RUN mkdir -p /var/www/certbot

EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
