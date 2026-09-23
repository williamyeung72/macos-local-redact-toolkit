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
        let entityMap = req.entity_map ?? [:]
        let instructions = req.instructions ?? ""
        let mapJSON = String(data: try JSONEncoder().encode(entityMap), encoding: .utf8) ?? "{}"
        let prompt = """
        \(instructions)

        Existing entity_map JSON (honour these tokens):
        \(mapJSON)

        Return a JSON object only, no markdown fences, with keys:
        - text: the redacted document
        - entity_map: object mapping every original string to its placeholder (existing plus new)

        Document:
        \(text)
        """
        let session = LanguageModelSession()
        let response = try await session.respond(to: prompt)
        let jsonText = unwrapFences(response.content)
        guard let outData = jsonText.data(using: .utf8),
              let obj = try JSONSerialization.jsonObject(with: outData) as? [String: Any],
              let outText = obj["text"] as? String,
              let map = obj["entity_map"] as? [String: String]
        else {
            emitFailure("Apple Intelligence returned a result that was not valid redaction JSON")
            exit(1)
        }
        emitSuccess(text: outText, entityMap: map)
    }

    static func vision(_ req: Request) async throws {
        requireAppleIntelligence()
        guard let b64 = req.image_b64, let raw = Data(base64Encoded: b64) else {
            emitFailure("vision_markdown missing image")
            exit(1)
        }
        let ocr = try ocrText(from: raw)
        let instructions = req.instructions ?? "Convert the extracted text into clean Markdown."
        let prompt = """
        \(instructions)

        The following text was recognized from an image. Produce clean Markdown only, no preamble.

        \(ocr)
        """
        let session = LanguageModelSession()
        let response = try await session.respond(to: prompt)
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

    static func unwrapFences(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("```") {
            if let firstNL = s.firstIndex(of: "\n") {
                s = String(s[s.index(after: firstNL)...])
            }
            if s.hasSuffix("```") {
                s = String(s.dropLast(3))
            }
        }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
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
