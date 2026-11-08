package capacity

// Liters converts dimensions in centimeters to liters.
func Liters(width, height, depth float64) float64 {
    return width * height * depth
}
