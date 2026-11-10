import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class LedgerTest {
    @Test void allocatesArchive() {
        byte[][] pages = new byte[512][];
        for (int i = 0; i < pages.length; i++) pages[i] = new byte[1024 * 1024];
        assertEquals(512, pages.length);
    }
}
