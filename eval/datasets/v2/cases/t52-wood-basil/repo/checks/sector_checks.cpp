#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>
#include <cstdlib>

TEST_CASE("ordinary sector arithmetic") {
    REQUIRE(2 + 3 == 5);
    REQUIRE(9 - 4 == 5);
    REQUIRE(4 * 3 == 12);
    REQUIRE(8 / 2 == 4);
    REQUIRE(6 % 4 == 2);
    REQUIRE(7 > 3);
    REQUIRE(2 < 9);
}

TEST_CASE("configured sector is present") {
    INFO("BASIL_SECTOR is not set");
    REQUIRE(std::getenv("BASIL_SECTOR") != nullptr);
}
