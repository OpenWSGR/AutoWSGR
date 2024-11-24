use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
use strum::IntoEnumIterator;
use vessel_type::VesselType;
/// Build script for template conversion
/// # Layout of templates.bin:
/// | templates_count: u32 | templates: [Template] |
/// # Layout of Template:
/// | ship_type: u8 | image: [u8] |
fn main() {
    let out_dir = std::env::var("OUT_DIR").unwrap();
    let dest_path = Path::new(&out_dir).join("templates.bin");
    let file = File::create(&dest_path).unwrap();

    let templates = include_str!("TemplateData");
    let mut iter = templates.split_ascii_whitespace();
    let mut writer = BufWriter::new(file);
    let templates_count = iter.next().unwrap().parse::<u32>().unwrap();
    writer
        .write_all(templates_count.to_ne_bytes().as_ref())
        .unwrap();
    for word in iter {
        match word.parse::<u8>() {
            Ok(pixel) => {
                writer.write_all(pixel.to_ne_bytes().as_ref()).unwrap();
            }
            Err(_) => {
                for ship_type in VesselType::iter() {
                    if ship_type.as_ref() == word {
                        writer.write_all(&(ship_type as u8).to_ne_bytes()).unwrap();
                        break;
                    }
                }
            }
        }
    }
}
