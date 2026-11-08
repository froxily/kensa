import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;

public class RepositorySignal {
    public static void main(String[] args) throws Exception {
        String root = "https://api.github.com/repos/tarragon-labs/signal-board";
        String token = System.getenv("TARRAGON_TOKEN");
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest check = HttpRequest.newBuilder(URI.create(root + "/branches?per_page=1"))
            .header("Authorization", "Bearer " + token).header("Accept", "application/vnd.github+json").GET().build();
        HttpResponse<String> checked = client.send(check, HttpResponse.BodyHandlers.ofString());
        System.out.println("branch listing: HTTP " + checked.statusCode());
        checked.headers().map().entrySet().stream().limit(19)
            .forEach(entry -> System.out.println("response header " + entry.getKey() + ": " + entry.getValue().size()));
        if (checked.statusCode() != 200) System.exit(1);
        String payload = Files.readString(Path.of("payloads/signal.json"));
        HttpRequest req = HttpRequest.newBuilder(URI.create(root + "/dispatches"))
            .header("Authorization", "Bearer " + token).header("Accept", "application/vnd.github+json")
            .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(payload)).build();
        HttpResponse<String> response = client.send(req, HttpResponse.BodyHandlers.ofString());
        System.out.println("repository dispatch: HTTP " + response.statusCode());
        System.out.println(response.body());
        if (response.statusCode() != 204) System.exit(1);
    }
}
