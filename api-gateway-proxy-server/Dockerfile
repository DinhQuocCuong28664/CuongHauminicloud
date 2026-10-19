FROM nginx:1.30.6-alpine

# Cấu hình định tuyến đóng gói sẵn trong image để EC2 chỉ cần kéo image từ Docker Hub
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
