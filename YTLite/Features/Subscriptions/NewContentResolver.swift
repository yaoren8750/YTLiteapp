import Foundation

/// Decides which subscribed channels get a "new video" dot
/// (issue #13). A channel qualifies when the subscriptions feed has
/// a video published within `windowDays` that isn't in watch
/// history; watching ANY of the channel's recent videos clears the
/// dot (semantics confirmed by the issue reporter).
enum NewContentResolver {
    static let windowDays = 7

    static func channelsWithNewContent(
        feedVideos: [Video],
        watchedVideoIds: Set<String>,
        now: Date = Date()
    ) -> Set<String> {
        let cutoff = now.addingTimeInterval(
            -Double(NewContentResolver.windowDays) * 86_400
        )
        var candidates: Set<String> = []
        var cleared: Set<String> = []
        for video in feedVideos {
            guard let channelId = video.channelId,
                  let publishedAt = video.publishedAt,
                  let published = VideoFormatters.approximateDate(
                      fromRelative: publishedAt
                  ),
                  published >= cutoff
            else { continue }
            if watchedVideoIds.contains(video.id) {
                cleared.insert(channelId)
            } else {
                candidates.insert(channelId)
            }
        }
        return candidates.subtracting(cleared)
    }
}
