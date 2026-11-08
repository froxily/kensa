import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;

public class CatalogStatus {
    public static void main(String[] args) throws Exception {
        String endpoint = Files.readString(Path.of("settings/catalog-url.txt")).trim();
        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint)).GET().build();
        HttpResponse<String> response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200 || !response.body().contains("ready")) System.exit(1);
    }
}
