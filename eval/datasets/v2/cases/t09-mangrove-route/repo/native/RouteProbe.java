import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;

public class RouteProbe {
    public static void main(String[] args) throws Exception {
        for (String bucket : Files.readAllLines(Path.of("data/buckets.txt"))) {
            System.out.println("loaded bucket " + bucket);
        }
        String configured = System.getenv("MANGROVE_CACHE_HOST");
        String host;
        if (configured == null || configured.isBlank()) {
            System.err.println("MANGROVE_CACHE_HOST is not set");
            host = "mangrove-cache.internal";
        } else {
            host = configured;
        }
        try (Socket socket = new Socket(host, 6435)) {
            System.out.println("cache connected: " + socket.isConnected());
        }
    }
}
