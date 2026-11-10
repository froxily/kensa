import java.util.LinkedHashMap;
import java.util.Map;

public class AtlasIndex {
    public static void main(String[] args) {
        Map<Integer, byte[]> cache = new LinkedHashMap<>();
        for (int page = 0; page < 512; page++) {
            cache.put(page, new byte[1024 * 1024]);
        }
        System.out.println("Indexed " + cache.size() + " pages");
    }
}
