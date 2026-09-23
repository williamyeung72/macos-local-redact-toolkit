import Foundation
import FoundationModels

struct Request: Decodable {
    var op: String
    var text: String
    var entity_map: [String: String]
    var instructions: String
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
        guard req.op == "redact_chunk" else {
            emitFailure("Unsupported op")
            exit(1)
        }

        let model = SystemLanguageModel.default
        switch model.availability {
        case .available:
            break
        default:
            emitFailure("Apple Intelligence is unavailable on this Mac")
            exit(1)
        }

        let mapJSON = String(
            data: try JSONEncoder().encode(req.entity_map),
            encoding: .utf8
        ) ?? "{}"

        let prompt = """
        \(req.instructions)

        Existing entity_map JSON (honour these tokens):
        \(mapJSON)

        Return a JSON object only, no markdown fences, with keys:
        - text: the redacted document
        - entity_map: object mapping every original string to its placeholder (existing plus new)

        Document:
        \(req.text)
        """

        let session = LanguageModelSession()
        let response = try await session.respond(to: prompt)
        let raw = response.content.trimmingCharacters(in: .whitespacesAndNewlines)
        let jsonText = unwrapFences(raw)
        guard let outData = jsonText.data(using: .utf8),
              let obj = try JSONSerialization.jsonObject(with: outData) as? [String: Any],
              let text = obj["text"] as? String,
              let map = obj["entity_map"] as? [String: String]
        else {
            emitFailure("Apple Intelligence returned a result that was not valid redaction JSON")
            exit(1)
        }

        let payload = Success(ok: true, text: text, entity_map: map)
        let encoded = try JSONEncoder().encode(payload)
        FileHandle.standardOutput.write(encoded)
    }

    static func unwrapFences(_ raw: String) -> String {
        var s = raw
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

    static func emitFailure(_ message: String) {
        let payload = Failure(ok: false, error: message)
        if let encoded = try? JSONEncoder().encode(payload) {
            FileHandle.standardOutput.write(encoded)
            FileHandle.standardOutput.write(Data("\n".utf8))
        }
        FileHandle.standardError.write(Data("\(message)\n".utf8))
    }
}
