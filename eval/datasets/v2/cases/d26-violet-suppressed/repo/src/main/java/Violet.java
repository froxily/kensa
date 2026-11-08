import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class Violet {
    public static void main(String[] args) throws Exception {
        String source = System.getenv("VIOLET_SOURCE");
        HttpRequest request = HttpRequest.newBuilder(URI.create(source)).GET().build();
        var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.discarding());
        if (response.statusCode() != 200) System.exit(1);
    }
}
