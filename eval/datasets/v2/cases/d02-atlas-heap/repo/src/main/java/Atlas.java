import java.util.ArrayList;

public class Atlas {
    public static void main(String[] args) {
        var pages = new ArrayList<byte[]>();
        for (int i = 0; i < 100; i++) pages.add(new byte[1024 * 1024]);
        System.out.println(pages.size());
    }
}
