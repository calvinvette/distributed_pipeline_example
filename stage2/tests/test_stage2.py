import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "stage2" / "src"))


class TestStage2Normalization:
    def test_parse_sizes(self):
        from stage2 import Stage2Config
        
        config = Stage2Config.__new__(Stage2Config)
        sizes = config._parse_sizes("1080p,720p,800x600")
        
        assert len(sizes) == 3
        assert sizes[0] == ("1080p", 1920, 1080)
        assert sizes[1] == ("720p", 1280, 720)
        assert sizes[2] == ("800x600", 800, 600)

    def test_resize_image(self):
        import numpy as np
        from stage2 import resize_image
        
        img = np.random.randint(0, 255, (1000, 1500, 3), dtype=np.uint8)
        
        resized = resize_image(img, 800, 600)
        
        assert resized.shape == (600, 800, 3)

    def test_resize_preserves_aspect_ratio(self):
        import numpy as np
        from stage2 import resize_image
        
        img = np.zeros((1000, 2000, 3), dtype=np.uint8)
        
        resized = resize_image(img, 1280, 720)
        
        assert resized.shape == (720, 1280, 3)
