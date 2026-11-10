package org.larchfield;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GaugeTest {
    @Test void fullAtCapacity() {
        assertTrue(Gauge.isFull(12, 12));
    }
}
