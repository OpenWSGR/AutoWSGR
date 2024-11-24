use crate::interface::WrappedPixels;

pub struct Pixel<'i> {
    pub pixel: &'i [u8],
}
impl<'i> Pixel<'i> {
    pub fn is_key_color(&self, key_colors: &[Pixel], threshold: f64) -> bool {
        for key_color in key_colors {
            let distance = self.cacl_distance(key_color);
            if distance < threshold {
                return true;
            }
        }
        false
    }
    fn cacl_distance(&self, other: &Pixel) -> f64 {
        let mut distant = 0f64;
        for (&a, &b) in self.pixel.iter().zip(other.pixel.iter()) {
            let diff = a as f64 - b as f64;
            distant += diff * diff;
        }
        distant.sqrt()
    }
}
pub struct BGRImage<'i> {
    width: usize,
    height: usize,
    channels: usize,
    pixels: &'i [u8],
}
impl<'i> BGRImage<'i> {
    pub fn from_wrapped_pixels(wrapped_pixels: WrappedPixels<'i>) -> Self {
        assert_eq!(wrapped_pixels.channels, 3);
        Self {
            width: wrapped_pixels.width,
            height: wrapped_pixels.height,
            channels: wrapped_pixels.channels,
            pixels: wrapped_pixels.pixels,
        }
    }
    pub fn get_width(&self) -> usize {
        self.width
    }
    pub fn get_height(&self) -> usize {
        self.height
    }
    pub fn get_pixel(&self, y: usize, x: usize) -> Pixel {
        let index = (y * self.width + x) * self.channels;
        let pixel = &self.pixels[index..index + self.channels];
        Pixel { pixel }
    }
}
