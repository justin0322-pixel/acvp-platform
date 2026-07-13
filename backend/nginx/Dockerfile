FROM nginx:alpine
RUN rm /etc/nginx/conf.d/default.conf
# The nginx image renders /etc/nginx/templates/*.template with envsubst at
# start, injecting ${PROXY_SECRET} from the environment (see nginx.conf.template).
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 8080 8443
