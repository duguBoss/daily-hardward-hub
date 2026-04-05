import unittest

from daily_hardware.filters import is_hardware_project


class HardwareFilterTest(unittest.TestCase):
    def test_accepts_hardware_and_3d_print_projects(self) -> None:
        self.assertTrue(is_hardware_project("ESP32 Smart Sensor Board", "PCB, IoT, 3D printed enclosure"))

    def test_rejects_food_projects(self) -> None:
        self.assertFalse(is_hardware_project("How to Bake Chocolate Cookies", "Easy dessert recipe and baking steps"))


if __name__ == "__main__":
    unittest.main()
