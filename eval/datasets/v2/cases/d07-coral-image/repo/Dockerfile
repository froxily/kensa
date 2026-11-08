FROM php:8.3-cli AS runtime
WORKDIR /srv
COPY public/ public/
COPY --from=assets /out/style.css public/style.css
CMD ["php", "-S", "0.0.0.0:8080", "-t", "public"]
