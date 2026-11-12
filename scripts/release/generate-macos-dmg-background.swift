#!/usr/bin/env swift

import AppKit
import Foundation

private let canvasWidth = 660
private let canvasHeight = 440

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("error: \(message)\n".utf8))
    exit(1)
}

guard CommandLine.arguments.count == 3 || CommandLine.arguments.count == 4 else {
    fail("usage: generate-macos-dmg-background.swift BRAND.png OUTPUT.png [1|2]")
}

let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
let outputScale = CommandLine.arguments.count == 4 ? Int(CommandLine.arguments[3]) : 1
guard outputScale == 1 || outputScale == 2 else {
    fail("background scale must be 1 or 2")
}
guard let brand = NSImage(contentsOf: inputURL) else {
    fail("could not read \(inputURL.path)")
}

func rasterize(_ image: NSImage) -> NSBitmapImageRep {
    let width = max(Int(image.size.width.rounded()), 1)
    let height = max(Int(image.size.height.rounded()), 1)
    guard let bitmap = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: width,
        pixelsHigh: height,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bitmapFormat: [],
        bytesPerRow: 0,
        bitsPerPixel: 0
    ), let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        fail("could not rasterize the Church Cap brand")
    }
    bitmap.size = NSSize(width: width, height: height)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    NSColor.clear.setFill()
    NSRect(x: 0, y: 0, width: width, height: height).fill()
    image.draw(in: NSRect(x: 0, y: 0, width: width, height: height), from: .zero, operation: .copy, fraction: 1)
    context.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    return bitmap
}

func visibleBounds(_ bitmap: NSBitmapImageRep) -> NSRect {
    var minX = bitmap.pixelsWide
    var minY = bitmap.pixelsHigh
    var maxX = -1
    var maxY = -1
    for y in 0..<bitmap.pixelsHigh {
        for x in 0..<bitmap.pixelsWide where (bitmap.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.02 {
            minX = min(minX, x)
            minY = min(minY, y)
            maxX = max(maxX, x)
            maxY = max(maxY, y)
        }
    }
    guard maxX >= minX, maxY >= minY else { fail("the brand image is empty") }
    return NSRect(x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1)
}

guard let output = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: canvasWidth * outputScale!,
    pixelsHigh: canvasHeight * outputScale!,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bitmapFormat: [],
    bytesPerRow: 0,
    bitsPerPixel: 0
), let graphics = NSGraphicsContext(bitmapImageRep: output) else {
    fail("could not allocate the DMG background")
}

// tiffutil expects the HiDPI source to be twice the pixel dimensions while
// retaining 72-DPI metadata. Finder then selects the correct TIFF layer.
output.size = NSSize(
    width: canvasWidth * outputScale!,
    height: canvasHeight * outputScale!
)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = graphics
let cg = graphics.cgContext
cg.scaleBy(x: CGFloat(outputScale!), y: CGFloat(outputScale!))
let canvas = NSRect(x: 0, y: 0, width: canvasWidth, height: canvasHeight)

let base = NSGradient(colorsAndLocations:
    (NSColor(calibratedRed: 0.975, green: 0.99, blue: 1.0, alpha: 1), 0.0),
    (NSColor(calibratedRed: 0.945, green: 0.975, blue: 0.995, alpha: 1), 0.56),
    (NSColor(calibratedRed: 0.955, green: 0.945, blue: 1.0, alpha: 1), 1.0)
)!
base.draw(in: canvas, angle: 0)

let colourSpace = CGColorSpaceCreateDeviceRGB()
func glow(colour: NSColor, centre: CGPoint, radius: CGFloat) {
    let gradient = CGGradient(
        colorsSpace: colourSpace,
        colors: [colour.cgColor, colour.withAlphaComponent(0).cgColor] as CFArray,
        locations: [0, 1]
    )!
    cg.drawRadialGradient(
        gradient,
        startCenter: centre,
        startRadius: 0,
        endCenter: centre,
        endRadius: radius,
        options: [.drawsAfterEndLocation]
    )
}
glow(colour: NSColor(calibratedRed: 0.11, green: 0.70, blue: 0.88, alpha: 0.13), centre: CGPoint(x: 90, y: 380), radius: 330)
glow(colour: NSColor(calibratedRed: 0.43, green: 0.20, blue: 0.94, alpha: 0.12), centre: CGPoint(x: 610, y: 55), radius: 340)

let brandBitmap = rasterize(brand)
let pixelBounds = visibleBounds(brandBitmap)
let drawBounds = NSRect(
    x: pixelBounds.minX,
    y: CGFloat(brandBitmap.pixelsHigh) - pixelBounds.maxY,
    width: pixelBounds.width,
    height: pixelBounds.height
)
let brandImage = NSImage(size: brandBitmap.size)
brandImage.addRepresentation(brandBitmap)
let brandWidth: CGFloat = 205
let brandHeight = brandWidth * drawBounds.height / drawBounds.width
brandImage.draw(
    in: NSRect(x: (CGFloat(canvasWidth) - brandWidth) / 2, y: 356, width: brandWidth, height: brandHeight),
    from: drawBounds,
    operation: .sourceOver,
    fraction: 1,
    respectFlipped: false,
    hints: [.interpolation: NSImageInterpolation.high]
)

let centred = NSMutableParagraphStyle()
centred.alignment = .center
func drawCentred(_ value: String, y: CGFloat, font: NSFont, colour: NSColor) {
    value.draw(
        in: NSRect(x: 30, y: y, width: CGFloat(canvasWidth) - 60, height: font.pointSize * 1.5),
        withAttributes: [.font: font, .foregroundColor: colour, .paragraphStyle: centred]
    )
}
drawCentred("Install Church Cap", y: 313, font: .systemFont(ofSize: 27, weight: .bold), colour: NSColor(calibratedRed: 0.07, green: 0.095, blue: 0.15, alpha: 1))
drawCentred("Drag Church Cap into the Applications folder", y: 282, font: .systemFont(ofSize: 15, weight: .medium), colour: NSColor(calibratedRed: 0.27, green: 0.33, blue: 0.41, alpha: 1))

for centreX in [165.0, 495.0] {
    // Finder chooses dark labels in light system appearance. Extend the white
    // glass cards below the icons so both item names remain highly legible.
    let halo = NSBezierPath(roundedRect: NSRect(x: centreX - 76, y: 74, width: 152, height: 192), xRadius: 36, yRadius: 36)
    NSColor(calibratedWhite: 1, alpha: 0.94).setFill()
    halo.fill()
    NSColor(calibratedWhite: 1, alpha: 0.94).setStroke()
    halo.lineWidth = 1
    halo.stroke()
}

let arrow = NSBezierPath()
arrow.move(to: NSPoint(x: 255, y: 192))
arrow.line(to: NSPoint(x: 407, y: 192))
arrow.move(to: NSPoint(x: 407, y: 192))
arrow.line(to: NSPoint(x: 383, y: 211))
arrow.move(to: NSPoint(x: 407, y: 192))
arrow.line(to: NSPoint(x: 383, y: 173))
arrow.lineCapStyle = .round
arrow.lineJoinStyle = .round
arrow.lineWidth = 5
NSColor(calibratedRed: 0.10, green: 0.37, blue: 0.71, alpha: 0.94).setStroke()
arrow.stroke()

drawCentred("DRAG TO INSTALL", y: 223, font: .systemFont(ofSize: 11, weight: .bold), colour: NSColor(calibratedRed: 0.10, green: 0.37, blue: 0.71, alpha: 1))
drawCentred("churchcap.org", y: 27, font: .systemFont(ofSize: 11, weight: .medium), colour: NSColor(calibratedRed: 0.31, green: 0.37, blue: 0.45, alpha: 1))

graphics.flushGraphics()
NSGraphicsContext.restoreGraphicsState()
guard let png = output.representation(using: .png, properties: [:]) else {
    fail("could not encode the DMG background")
}
do {
    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try png.write(to: outputURL, options: .atomic)
    print("created: \(outputURL.path)")
} catch {
    fail("could not write \(outputURL.path): \(error.localizedDescription)")
}
