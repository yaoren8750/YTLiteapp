import Foundation

// MARK: - Fetch

extension MWebSource {
    /// Mints the GVS pot bound to the VIDEO ID — YouTube's current experiment
    /// binds the mweb pot to the video id, not visitorData (verified against
    /// yt-dlp + BgUtils). Runs concurrently with /player + n-solving; the
    /// build step waits on `potWait` before injecting the pot into the URLs.
    func mintPot(videoId: String) {
        potWait.enter()
        poTokenService.fetchSessionToken(identifier: videoId) { [weak self] result in
            switch result {
            case .success(let token):
                AppLog.player("mwebSource: minted pot for videoId (\(token.prefix(12))…)")
                self?.poToken = token
            case .failure(let error):
                AppLog.player("mwebSource: pot mint failed: \(error)")
                self?.poToken = nil
            }
            self?.potWait.leave()
        }
    }

    func fetchPlayback(
        videoId: String,
        cancellation: CancellationToken?,
        completion: @escaping (Result<PreparedPlayback, Error>) -> Void
    ) {
        apiClient.fetchMWebPlayback(
            videoId: videoId,
            poToken: poToken,
            visitorData: visitorData,
            signatureTimestamp: Self.cachedSTS,
            cancellationToken: cancellation
        ) { [weak self] result in
            switch result {
            case .failure(let error):
                self?.retryWithFreshPot(
                    videoId: videoId,
                    error: error,
                    cancellation: cancellation,
                    completion: completion
                )
            case .success(let info):
                self?.handleInfo(info, completion: completion)
            }
        }
    }

    // MARK: - Private

    /// A /player rejection with a previously working pot means the cached
    /// token went stale (GVS bot-check answers LOGIN_REQUIRED / zero formats).
    /// Invalidate it and retry ONCE with a forced fresh mint.
    private func retryWithFreshPot(
        videoId: String,
        error: Error,
        cancellation: CancellationToken?,
        completion: @escaping (Result<PreparedPlayback, Error>) -> Void
    ) {
        guard !didRetryFreshPot, cancellation?.isCancelled != true else {
            completion(.failure(error))
            return
        }
        didRetryFreshPot = true
        AppLog.player("mwebSource: /player failed (\(error)), retrying with fresh pot")
        poTokenService.invalidateToken(identifier: videoId)
        mintPot(videoId: videoId)
        potWait.notify(queue: .main) { [weak self] in
            self?.fetchPlayback(
                videoId: videoId,
                cancellation: cancellation,
                completion: completion
            )
        }
    }

    private func handleInfo(
        _ info: DirectPlaybackInfo,
        completion: @escaping (Result<PreparedPlayback, Error>) -> Void
    ) {
        updateQualityState(from: info)
        AppLog.player(
            "mwebSource: reqVD=\((visitorData ?? "nil").prefix(24))"
                + " respVD=\((info.visitorData ?? "nil").prefix(24))"
        )
        guard let video = info.dashVideoFormat,
              let audio = info.dashAudioFormat else {
            loadLiveHLS(info: info, completion: completion)
            return
        }
        solveThenBuild(info: info, video: video, audio: audio, completion: completion)
    }
}
