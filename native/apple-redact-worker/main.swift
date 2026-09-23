import Foundation
import FoundationModels
import Vision
import AppKit

struct Request: Decodable {
    var op: String
    var text: String?
    var entity_map: [String: String]?
    var instructions: String?
    var image_b64: String?
    var mime: String?
}

struct Success: Encodable {
    var ok: Bool
    var text: String
    var entity_map: [String: String]
}

struct Failure: Encodable {
    var ok: Bool
    var error: String
}

@Generable
struct EntityEntry {
    @Guide(description: "Original sensitive string exactly as it appears in the document")
    var original: String
    @Guide(description: "Stable placeholder such as [PERSON_1], [EMAIL_2], or [PHONE_1]")
    var placeholder: String
}

@Generable
struct EntityExtraction {
    @Guide(description: "Sensitive spans found in the document; empty if none")
    var entities: [EntityEntry]
}

@main
struct AppleRedactWorker {
    static func main() async {
        do {
            try await run()
        } catch {
            emitFailure("Apple Intelligence worker failed: \(error.localizedDescription)")
            exit(1)
        }
    }

    static func run() async throws {
        guard let data = try FileHandle.standardInput.readToEnd(), !data.isEmpty else {
            emitFailure("Apple Intelligence worker received empty stdin")
            exit(1)
        }
        let req = try JSONDecoder().decode(Request.self, from: data)
        switch req.op {
        case "redact_chunk":
            try await redact(req)
        case "vision_markdown":
            try await vision(req)
        default:
            emitFailure("Unsupported op")
            exit(1)
        }
    }

    static func requireAppleIntelligence() {
        switch SystemLanguageModel.default.availability {
        case .available:
            return
        default:
            emitFailure("Apple Intelligence is unavailable on this Mac")
            exit(1)
        }
    }

    static func redact(_ req: Request) async throws {
        requireAppleIntelligence()
        let text = req.text ?? ""
        var entityMap = req.entity_map ?? [:]
        let instructions = req.instructions ?? ""
        let mapJSON = String(data: try JSONEncoder().encode(entityMap), encoding: .utf8) ?? "{}"

        let session = LanguageModelSession(instructions: """
        \(instructions)

        Existing entity_map JSON (reuse these placeholders for the same originals; do not renumber them):
        \(mapJSON)

        Extract sensitive spans only. Do not rewrite the document.
        """)

        let response: LanguageModelSession.Response<EntityExtraction>
        do {
            response = try await session.respond(
                to: """
                List every sensitive span in this document chunk. If none, return an empty entities array.

                Document:
                \(text)
                """,
                generating: EntityExtraction.self
            )
        } catch {
            let msg = String(describing: error)
            if msg.localizedCaseInsensitiveContains("exceededContextWindowSize")
                || msg.localizedCaseInsensitiveContains("context window") {
                emitFailure(
                    "Apple Intelligence context window exceeded; try a smaller REDACT_CHUNK_CHARS value"
                )
                exit(1)
            }
            throw error
        }

        for entry in response.content.entities {
            let original = entry.original.trimmingCharacters(in: .whitespacesAndNewlines)
            let placeholder = entry.placeholder.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !original.isEmpty, !placeholder.isEmpty else { continue }
            if entityMap[original] == nil {
                entityMap[original] = placeholder
            }
        }

        let redacted = applyReplacements(text, entityMap: entityMap)
        emitSuccess(text: redacted, entityMap: entityMap)
    }

    /// Apply longer originals first so partial overlaps do not corrupt longer matches.
    static func applyReplacements(_ text: String, entityMap: [String: String]) -> String {
        guard !entityMap.isEmpty else { return text }
        let pairs = entityMap.sorted { $0.key.count > $1.key.count }
        var out = text
        for (original, placeholder) in pairs {
            out = out.replacingOccurrences(of: original, with: placeholder)
        }
        return out
    }

    static func vision(_ req: Request) async throws {
        requireAppleIntelligence()
        guard let b64 = req.image_b64, let raw = Data(base64Encoded: b64) else {
            emitFailure("vision_markdown missing image")
            exit(1)
        }
        let ocr = try ocrText(from: raw)
        let instructions = req.instructions ?? "Convert the extracted text into clean Markdown."
        let session = LanguageModelSession(instructions: instructions)
        let response = try await session.respond(
            to: "The following text was recognized from an image. Produce clean Markdown only, no preamble.\n\n\(ocr)"
        )
        let md = response.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !md.isEmpty else {
            emitFailure("Apple visual understanding returned empty markdown")
            exit(1)
        }
        emitSuccess(text: md, entityMap: [:])
    }

    static func ocrText(from data: Data) throws -> String {
        guard let image = NSImage(data: data),
              let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
        else {
            throw NSError(domain: "apple-redact-worker", code: 2, userInfo: [
                NSLocalizedDescriptionKey: "Could not decode image",
            ])
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["zh-Hant", "zh-Hans", "en-US"]
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try handler.perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return lines.joined(separator: "\n")
    }

    static func emitSuccess(text: String, entityMap: [String: String]) {
        let payload = Success(ok: true, text: text, entity_map: entityMap)
        if let encoded = try? JSONEncoder().encode(payload) {
            FileHandle.standardOutput.write(encoded)
        }
    }

    static func emitFailure(_ message: String) {
        let payload = Failure(ok: false, error: message)
        if let encoded = try? JSONEncoder().encode(payload) {
            FileHandle.standardOutput.write(encoded)
            FileHandle.standardOutput.write(Data("\n".utf8))
        }
        FileHandle.standardError.write(Data("\(message)\n".utf8))
    }
}
