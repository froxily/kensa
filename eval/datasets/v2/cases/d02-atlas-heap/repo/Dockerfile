FROM eclipse-temurin:21-jdk
WORKDIR /app
COPY src/ src/
RUN javac -d out src/main/java/Atlas.java
RUN java -Xmx32m -cp out Atlas
