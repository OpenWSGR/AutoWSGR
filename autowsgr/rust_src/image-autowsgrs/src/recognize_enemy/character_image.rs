use crate::interface::WrappedPixels;

use super::{templates::Template, HEIGHT, WIDTH};

#[derive(Debug, Clone, Copy)]
pub enum MatchMethod {
    First,
    Last,
    All,
}

#[derive(Debug, Clone)]
pub struct CharacterImage {
    pub width: usize,
    pub height: usize,
    pub pixels: [[f64; WIDTH]; HEIGHT],
    pub brightness: f64,
}
impl CharacterImage {
    pub fn from_wrapped_pixels(wrapped_pixels: WrappedPixels) -> Self {
        let width = wrapped_pixels.width;
        let height = wrapped_pixels.height;
        assert_eq!(wrapped_pixels.channels, 1);
        let pixels = wrapped_pixels.pixels;
        assert_eq!(width, WIDTH);
        assert_eq!(height, HEIGHT);
        let mut sum = 0f64;
        let mut image = CharacterImage {
            width,
            height,
            pixels: [[0f64; WIDTH]; HEIGHT],
            brightness: 0f64,
        };
        for i in 0..height {
            for j in 0..width {
                let pixel = pixels[i * width + j];
                image.pixels[i][j] = pixel as f64;
                sum += pixel as f64;
            }
        }
        image.brightness = sum;
        image.process();
        image
    }
    fn process(&mut self) {
        let mut sum = 0f64;
        for row in &mut self.pixels {
            for pixel in row {
                if *pixel > self.brightness / self.width as f64 / self.height as f64 * 1.2 {
                    *pixel += 10f64;
                }
                if *pixel < self.brightness / self.width as f64 / self.height as f64 * 0.8 {
                    *pixel -= 10f64;
                }
                sum += *pixel;
            }
        }
        for row in &mut self.pixels {
            for pixel in row {
                *pixel /= sum;
            }
        }
    }

    pub fn calc_image_diffreance(&self, template: &Template, method: MatchMethod) -> f64 {
        if self.brightness.max(template.image.brightness)
            / self.brightness.min(template.image.brightness)
            >= 3f64
        {
            return 1f64;
        }
        let match_start;
        let match_end;
        match method {
            MatchMethod::First => {
                match_start = 0;
                match_end = self.width / 2;
            }
            MatchMethod::Last => {
                match_start = self.width / 2;
                match_end = self.width;
            }
            MatchMethod::All => {
                match_start = 0;
                match_end = self.width;
            }
        }
        let mut diff = 1000f64;
        for i in -1..=1 {
            for j in -1..=1 {
                let mut now = 0f64;
                for pa2 in 0..self.height as i32 {
                    for pa1 in 0..match_end as i32 {
                        let pb1 = pa1 + i;
                        let pb2 = pa2 + j;
                        if pb1 < match_end as i32
                            && pb2 < self.height as i32
                            && pb1 >= match_start as i32
                            && pb2 >= 0
                        {
                            let a = self.pixels[pa2 as usize][pa1 as usize];
                            let b = template.image.pixels[pb2 as usize][pb1 as usize];
                            now += (a - b).abs();
                        }
                    }
                }
                diff = diff.min(now);
            }
        }
        diff
    }
}
