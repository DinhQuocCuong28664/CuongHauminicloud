FROM nginx:1.30.6-alpine

LABEL org.opencontainers.image.title="myminicloud-proxy" \
      org.opencontainers.image.description="MyMiniCloud reverse proxy / load balancer: nginx" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

# Cấu hình định tuyến đóng gói sẵn trong image để EC2 chỉ cần kéo image từ Docker Hub
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
