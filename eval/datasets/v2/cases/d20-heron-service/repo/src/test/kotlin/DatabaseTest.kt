import org.junit.jupiter.api.Test
import java.net.Socket

class DatabaseTest {
    @Test
    fun databaseAcceptsConnections() {
        Socket("127.0.0.1", 3306).use { socket ->
            check(socket.isConnected)
        }
    }
}
