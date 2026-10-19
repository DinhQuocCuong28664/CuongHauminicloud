FROM nginx:1.30.6-alpine

# Tên bản sao (web1/web2) hiển thị trên trang và trong header X-Served-By,
# để thấy được proxy cân bằng tải luân phiên giữa hai web server
ENV SERVER_NAME=web1

RUN rm -f /etc/nginx/conf.d/default.conf
# Ảnh nginx tự chạy envsubst trên /etc/nginx/templates/*.template khi khởi động,
# kết quả ghi vào /etc/nginx/conf.d/default.conf
COPY templates/default.conf.template /etc/nginx/templates/default.conf.template
COPY html/ /usr/share/nginx/html/
COPY 40-server-name.sh /docker-entrypoint.d/40-server-name.sh
RUN chmod 755 /docker-entrypoint.d/40-server-name.sh && chmod -R 755 /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
