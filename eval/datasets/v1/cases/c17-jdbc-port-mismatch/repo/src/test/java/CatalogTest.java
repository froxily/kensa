import java.sql.DriverManager;
import org.junit.Test;
import static org.junit.Assert.assertTrue;

public class CatalogTest {
  @Test public void connects() throws Exception {
    try (var c = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/catalog", "postgres", "testpass")) {
      assertTrue(c.isValid(2));
    }
  }
}
