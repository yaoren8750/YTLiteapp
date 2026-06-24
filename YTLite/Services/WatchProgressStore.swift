import Foundation

struct WatchProgress {
    let fraction: Double

    var shouldShow: Bool {
        fraction > 0.03
    }
}

/// Stores per-video watch progress from YouTube servers.
/// Populated by WatchProgressSyncService and inline
/// extraction from browse/feed responses.
final class WatchProgressStore {
    static let shared = WatchProgressStore()

    private let fractionKey = "WatchProgressStore.fractions"
    private let maxEntries = 200
    private let queue = DispatchQueue(
        label: "com.ytvlite.watch-progress",
        attributes: .concurrent
    )
    private var serverFractions: [String: Double] = [:]

    init() {
        loadFractions()
        UserDefaults.standard.removeObject(
            forKey: "WatchProgressStore.v1"
        )
    }

    func setFraction(
        videoId: String,
        fraction: Double
    ) {
        queue.async(flags: .barrier) {
            self.serverFractions[videoId] = fraction
            if self.serverFractions.count > self.maxEntries {
                let excess = self.serverFractions
                    .count - self.maxEntries
                self.serverFractions.keys
                    .prefix(excess)
                    .forEach {
                        self.serverFractions
                            .removeValue(forKey: $0)
                    }
            }
            self.persistFractions()
        }
    }

    func setServerFractions(
        _ entries: [String: Double]
    ) {
        queue.async(flags: .barrier) {
            self.serverFractions = entries
            self.persistFractions()
        }
    }

    func progress(
        forVideoId videoId: String
    ) -> WatchProgress? {
        guard let frac = queue.sync(execute: {
            serverFractions[videoId]
        }) else {
            return nil
        }
        return WatchProgress(fraction: frac)
    }

    func clearAll() {
        queue.async(flags: .barrier) {
            self.serverFractions.removeAll()
            UserDefaults.standard.removeObject(
                forKey: self.fractionKey
            )
        }
    }

    // MARK: - Persistence

    private func loadFractions() {
        guard let raw = UserDefaults.standard.dictionary(
            forKey: fractionKey
        ) as? [String: Double]
        else {
            return
        }
        serverFractions = raw
    }

    private func persistFractions() {
        UserDefaults.standard.set(
            serverFractions, forKey: fractionKey
        )
    }
}
