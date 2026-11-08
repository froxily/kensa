import org.junit.Test
import java.net.InetSocketAddress
import java.net.Socket

class PublishedPortTest {
    @Test fun connects() {
        Socket().use { it.connect(InetSocketAddress("127.0.0.1", 13306), 2000) }
    }
}
