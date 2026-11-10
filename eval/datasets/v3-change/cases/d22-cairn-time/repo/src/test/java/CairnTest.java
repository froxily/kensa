import org.junit.Test;
import static org.junit.Assert.assertEquals;
public class CairnTest {
    @Test public void sumsSamples() {
        long sum = 0;
        for (long i = 0; i < 1000000000000L; i++) sum += i % 2;
        assertEquals(500000000000L, sum);
    }
}
