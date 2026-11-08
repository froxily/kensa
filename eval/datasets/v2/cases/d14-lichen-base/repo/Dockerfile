FROM eclipse-temurin:21-jkd
WORKDIR /srv
COPY src/ src/
RUN javac -d out src/Lichen.java
CMD ["java", "-cp", "out", "Lichen"]
