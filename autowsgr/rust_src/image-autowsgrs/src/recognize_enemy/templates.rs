use crate::interface::WrappedPixels;

use super::CharacterImage;
use vessel_type::VesselType;
pub struct Template {
    pub ship_type: VesselType,
    pub image: CharacterImage,
}

impl Template {
    /// # Layout of templates.bin:
    /// | templates_count: u32 | templates: [Template] |
    /// # Layout of Template:
    /// | ship_type: u8 | image: [u8] |
    pub fn init_templates() -> Vec<Template> {
        let raw = include_bytes!(concat!(env!("OUT_DIR"), "/templates.bin"));
        let mut templates = Vec::new();
        let mut offset = 0;
        let template_count = u32::from_ne_bytes([
            raw[offset],
            raw[offset + 1],
            raw[offset + 2],
            raw[offset + 3],
        ]) as usize;
        offset += size_of::<u32>();
        for _ in 0..template_count {
            let ship_type = VesselType::from_repr(raw[offset] as usize).unwrap();
            offset += size_of::<u8>();
            let height = raw[offset] as usize;
            offset += size_of::<u8>();
            let width = raw[offset] as usize;
            offset += size_of::<u8>();
            let pixels = &raw[offset..offset + height * width];
            offset += height * width;
            let pixels = WrappedPixels {
                width,
                height,
                channels: 1,
                pixels,
            };
            let image = CharacterImage::from_wrapped_pixels(pixels);
            templates.push(Template { ship_type, image });
        }
        templates
    }
}
