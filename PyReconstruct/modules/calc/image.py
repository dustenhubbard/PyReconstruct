from pathlib import Path
from typing import List, Tuple, Sequence, Union

import cv2
import zarr

width = int
height = int

def getImgDims(img_fp: Union[str, Path]) -> Tuple[height, width]:
    """Return the pixel dimensions of an image."""

    if not isinstance(img_fp, Path):
        img_fp = Path(img_fp)
    
    if "scale_" in str(img_fp):

        z = zarr.open(img_fp)
        return z.shape
                
    else:

        img = cv2.imread(str(img_fp), cv2.IMREAD_GRAYSCALE)
        return img.shape


def point_2_pix(
        coordinate: Sequence[float],
        mag: float, height: height,
        subpix: bool=False
) -> Union[Tuple[float, float], Tuple[int, int]]:
            """Convert a single point to pixels."""

            x = coordinate[0] / mag
            y = height - (coordinate[1] / mag)

            if not subpix:
                
                x = int(x)
                y = int(y)
            
            return x, y


def point_list_2_pix(
        points: List[Tuple[int, int]],
        mag: float,
        height: int,
        subpix: bool=False
) -> List[Tuple[int, int]]:
    """Convert a points list to pixels."""
    
    mapped_points = map(lambda x: point_2_pix(x, mag, height, subpix), points)
    return list(mapped_points)
                
        
