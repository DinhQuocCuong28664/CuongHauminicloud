FROM nginx:1.30.6-alpine

LABEL org.opencontainers.image.title="myminicloud-web" \
      org.opencontainers.image.description="MyMiniCloud web server: nginx serving static pages and the blog" \
      org.opencontainers.image.authors="Đinh Quốc Cường (523H0008), Nguyễn Cao Hậu (523H0025)"

# Replica name (web1/web2) shown on the pages and in the X-Served-By header,
# so the proxy's round robin between the two web servers is visible
ENV SERVER_NAME=web1

RUN rm -f /etc/nginx/conf.d/default.conf
# The nginx image runs envsubst on /etc/nginx/templates/*.template at startup,
# writing the result to /etc/nginx/conf.d/default.conf
COPY templates/default.conf.template /etc/nginx/templates/default.conf.template
COPY html/ /usr/share/nginx/html/
COPY 40-server-name.sh /docker-entrypoint.d/40-server-name.sh
RUN chmod 755 /docker-entrypoint.d/40-server-name.sh && chmod -R 755 /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
