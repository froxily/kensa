import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;

public class Willow {
    public static void main(String[] args) throws Exception {
        var blocks = new ArrayList<byte[]>();
        for (int batch = 1; batch <= 100; batch++) {
            for (int part = 0; part < 4; part++) blocks.add(new byte[256 * 1024]);
            System.out.println("Built report batch " + batch);
        }
        Files.writeString(Path.of("out/report.txt"), "report ready\n");
    }
}
