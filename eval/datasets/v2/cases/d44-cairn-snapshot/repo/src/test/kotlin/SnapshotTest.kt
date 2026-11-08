import org.junit.jupiter.api.Test
import java.nio.file.Files
import java.nio.file.Path

class SnapshotTest {
    @Test
    fun buildsSnapshot() {
        val blocks = ArrayList<ByteArray>()
        for (batch in 1..100) {
            repeat(4) { blocks.add(ByteArray(256 * 1024)) }
            println("built segment $batch")
        }
        Files.writeString(Path.of("build/snapshot.txt"), "snapshot ready\n")
    }
}
